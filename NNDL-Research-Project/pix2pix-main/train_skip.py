import sys
import torch
from torch import nn
from torch.utils.data import DataLoader
import time
import argparse
from progress.bar import IncrementalBar
import csv
import datetime
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os

# Import dataset modules
from dataset import Cityscapes, Facades, Maps
from dataset import transforms as T

# Argument parser
parser = argparse.ArgumentParser(prog='top', description='Train Pix2Pix')
parser.add_argument("--epochs", type=int, default=200, help="Number of epochs")
parser.add_argument("--dataset", type=str, default="facades", help="Name of the dataset: ['facades', 'maps', 'cityscapes', 'all']")
parser.add_argument("--batch_size", type=int, default=1, help="Size of the batches")
parser.add_argument("--lr", type=float, default=0.0002, help="Adams learning rate")
parser.add_argument("--csv", action='store_true', help="Enable CSV logging")
parser.add_argument("--gan_folder", type=str, default="gan", choices=["gan", "gan_multiply", "gan_add"], help="Folder to import GAN from")
args = parser.parse_args()

# Append the chosen folder to the system path
sys.path.append(args.gan_folder)

# Now import the GAN modules from the specified folder
from generator import UnetGenerator
from discriminator import ConditionalDiscriminator
from criterion import GeneratorLoss, DiscriminatorLoss
from utils import Logger, initialize_weights



device = ('cuda:0' if torch.cuda.is_available() else 'cpu')

transforms = T.Compose([T.Resize((256,256)),
                        T.ToTensor(),
                        T.Normalize(mean=[0.5, 0.5, 0.5],
                                     std=[0.5, 0.5, 0.5])])

# Function to get dataset
def get_dataset(name):
    if name == 'cityscapes':
        return Cityscapes(root='.', transform=transforms, download=True, mode='train'), \
               Cityscapes(root='.', transform=transforms, download=True, mode='val')
    elif name == 'maps':
        return Maps(root='.', transform=transforms, download=True, mode='train'), \
               Maps(root='.', transform=transforms, download=True, mode='val')
    else:  # Default to 'facades'
        return Facades(root='.', transform=transforms, download=True, mode='train'), \
               Facades(root='.', transform=transforms, download=True, mode='val')

# Datasets to process
datasets_to_process = ['facades', 'maps', 'cityscapes'] if args.dataset == 'all' else [args.dataset]

for dataset_name in datasets_to_process:
    print(f'Downloading and processing "{dataset_name.upper()}" dataset!')

    # Initialize models for each dataset
    generator = UnetGenerator().to(device)
    discriminator = ConditionalDiscriminator().to(device)

    # Initialize optimizers for each dataset
    g_optimizer = torch.optim.Adam(generator.parameters(), lr=args.lr, betas=(0.5, 0.999))
    d_optimizer = torch.optim.Adam(discriminator.parameters(), lr=args.lr, betas=(0.5, 0.999))

    # Initialize loss functions
    g_criterion = GeneratorLoss(alpha=100)
    d_criterion = DiscriminatorLoss()

    # Load dataset
    train_dataset, val_dataset = get_dataset(dataset_name)
    train_dataloader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_dataloader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    csv_file = None
    csv_writer = None
    if args.csv:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = open(f'{dataset_name}_{timestamp}_training_log.csv', 'w', newline='')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['Epoch', ' G Training Loss', 'D Training Loss', 'G Validation Loss', 'Epoch Time (s)'])
        #csv_writer.writerow(['Epoch', ' G Training Loss', 'D Training Loss', 'G Validation Loss', 'D Validation Loss', 'Cur Val loss', 'Epoch Time (s)'])


    print('Start of training process for', dataset_name, 'dataset!')
    logger = Logger(filename=f'{dataset_name}_{args.epochs}_epochs_{args.batch_size}_bs_{args.lr}_lr')

    # Lists to store losses for plotting
    train_generator_losses = []
    train_discriminator_losses = []
    val_generator_losses = []
    val_discriminator_losses = []

    # Training loop
    best_val_loss = float('inf')
    epochs_since_improvement = 0
    for epoch in range(args.epochs):
        generator.train()
        discriminator.train()
        ge_loss=0.
        de_loss=0.
        start = time.time()
        bar = IncrementalBar(f'[Epoch {epoch+1}/{args.epochs}]', max=len(train_dataloader))
        for x, real in train_dataloader:
            x = x.to(device)
            real = real.to(device)

            # Generator`s loss
            fake = generator(x)
            fake_pred = discriminator(fake, x)
            g_loss = g_criterion(fake, real, fake_pred)

            # Discriminator`s loss
            fake = generator(x).detach()
            fake_pred = discriminator(fake, x)
            real_pred = discriminator(real, x)
            d_loss = d_criterion(fake_pred, real_pred)

            # Generator`s params update
            g_optimizer.zero_grad()
            g_loss.backward()
            g_optimizer.step()

            # Discriminator`s params update
            d_optimizer.zero_grad()
            d_loss.backward()
            d_optimizer.step()
            # add batch losses
            ge_loss += g_loss.item()
            de_loss += d_loss.item()
            bar.next()
        bar.finish()

        # Validation Step
        # generator.eval()
        # discriminator.eval()
        # ge_val_loss=0.
        # de_val_loss=0.

        # Break the training loop if validation loss hasn't improved for 10 epochs, (didnt use at the end)
        # if epochs_since_improvement >= 10:
        #    print(f"Early stopping triggered after {epoch + 1} epochs due to no improvement in validation loss")
        #    break

        # with torch.no_grad():
        #     bar = IncrementalBar(f'[Validation]', max=len(val_dataloader))
        #     for val_x, val_real in val_dataloader:
        #         val_x = val_x.to(device)
        #         val_real = val_real.to(device)
        #
        #         # Generator`s loss for validation
        #         val_fake = generator(val_x)
        #         val_fake_pred = discriminator(val_fake, val_x)
        #         val_g_loss = g_criterion(val_fake, val_real, val_fake_pred)
        #
        #         # Discriminator`s loss for validation
        #         val_fake = generator(val_x).detach()
        #         val_fake_pred = discriminator(val_fake, val_x)
        #         val_real_pred = discriminator(val_real, val_x)
        #         val_d_loss = d_criterion(val_fake_pred, val_real_pred)
        #
        #         # add batch losses
        #         ge_val_loss += val_g_loss.item()
        #         de_val_loss += val_d_loss.item()
        #         bar.next()
        #     bar.finish()

        # current_val_loss = (ge_val_loss + de_val_loss) / len(val_dataloader)
        # Early stopping check (didnt use at the end)
        # if current_val_loss < best_val_loss:
        #     best_val_loss = current_val_loss
        #     epochs_since_improvement = 0
        # else:
        #     epochs_since_improvement += 1

        # obtain per epoch losses for both training and validation
        # len(train_dataloader) is the number of train batches when batch size is args.batch_size
        # len(val_dataloader) is the number of val batches when batch size is args.batch_size
        g_loss = ge_loss / len(train_dataloader)
        d_loss = de_loss / len(train_dataloader)
        # val_g_loss = ge_val_loss / len(val_dataloader)
        # val_d_loss = de_val_loss / len(val_dataloader)

        # count timeframe
        end = time.time()
        tm = (end - start)

        # Append losses to the lists
        train_generator_losses.append(g_loss)
        train_discriminator_losses.append(d_loss)
        # val_generator_losses.append(val_g_loss)
        # val_discriminator_losses.append(val_d_loss)

        logger.add_scalar('generator_loss', g_loss, epoch+1)
        logger.add_scalar('discriminator_loss', d_loss, epoch+1)
        # logger.add_scalar('val_generator_loss', val_g_loss, epoch + 1)
        # logger.add_scalar('current_val_loss', current_val_loss, epoch + 1)

        # Save trained models
        logger.save_weights(generator.state_dict(), f'{dataset_name}_{args.epochs}_epochs_{args.batch_size}_bs_{args.lr}_lr_generator_base')
        logger.save_weights(discriminator.state_dict(), f'{dataset_name}_{args.epochs}_epochs_{args.batch_size}_bs_{args.lr}_lr_discriminator_base')

        if args.csv:
            csv_writer.writerow([epoch + 1,g_loss, d_loss, tm])
            # csv_writer.writerow([epoch + 1,g_loss, d_loss, val_g_loss, val_d_loss, current_val_loss, tm])
        print("[Epoch %d/%d] [G loss: %.3f] [D loss: %.3f] ETA: %.3fs"
            % (epoch + 1, args.epochs, g_loss, d_loss, tm))
        # print("[Epoch %d/%d] [G loss: %.3f] [D loss: %.3f] [Val G loss: %.3f] [Val D loss: %.3f] [Cur Val loss: %.3f] ETA: %.3fs"
        #     % (epoch + 1, args.epochs, g_loss, d_loss, val_g_loss, val_d_loss, current_val_loss, tm))

    logger.close()

    # Plot the training losses
    epochs_range = range(1, args.epochs + 1)
    fig, ax1 = plt.subplots(figsize=(10, 5))

    # Plot Discriminator Loss on the left y-axis
    ax1.plot(epochs_range, train_discriminator_losses, label='Training Discriminator Loss', color='blue')
    #ax1.plot(epochs_range, val_discriminator_losses, label='Validation Discriminator Loss', linestyle='dashed', color='blue')
    ax1.set_xlabel('Epochs')
    ax1.set_ylabel('Discriminator Loss', color='blue')
    ax1.tick_params(axis='y', labelcolor='blue')
    #ax1.legend(loc='upper left')

    # Create a secondary y-axis for Generator Loss on the right
    ax2 = ax1.twinx()
    ax2.plot(epochs_range, train_generator_losses, label='Training Generator Loss', color='green')
    #ax2.plot(epochs_range, val_generator_losses, label='Validation Generator Loss', linestyle='dashed', color='green')
    ax2.set_ylabel('Generator Loss', color='green')
    ax2.tick_params(axis='y', labelcolor='green')
    #ax2.legend(loc='upper right')

    ax1.xaxis.set_major_locator(MaxNLocator(integer=True)) # Set x-axis ticks as integer values
    plt.title(f'{dataset_name[0].upper()}{dataset_name[1:]} Train Losses ({args.batch_size} bs, {args.lr} lr)')
    #plt.legend()

    # Save the plot to a file
    save_dir = 'runs/plots/' + dataset_name
    os.makedirs(save_dir, exist_ok=True)
    plt.savefig(os.path.join(save_dir,f'{args.epochs}_epochs_{args.batch_size}_bs_{args.lr}_lr_train_plot.png'))
    plt.show()

    # # Plot the val losses
    # epochs_range = range(1, args.epochs + 1)
    # fig, ax1 = plt.subplots(figsize=(10, 5))
    #
    # # Plot Discriminator Loss on the left y-axis
    # ax1.plot(epochs_range, val_discriminator_losses, label='Validation Discriminator Loss', color='blue')
    # ax1.set_xlabel('Epochs')
    # ax1.set_ylabel('Discriminator Loss', color='blue')
    # ax1.tick_params(axis='y', labelcolor='blue')
    # #ax1.legend(loc='upper left')
    #
    # # Create a secondary y-axis for Generator Loss on the right
    # ax2 = ax1.twinx()
    # ax2.plot(epochs_range, val_generator_losses, label='Validation Generator Loss', color='green')
    # ax2.set_ylabel('Generator Loss', color='green')
    # ax2.tick_params(axis='y', labelcolor='green')
    # #ax2.legend(loc='upper right')
    #
    # ax1.xaxis.set_major_locator(MaxNLocator(integer=True)) # Set x-axis ticks as integer values
    # plt.title(f'{dataset_name[0].upper()}{dataset_name[1:]} Validation Losses ({args.batch_size} bs, {args.lr} lr)')
    # #plt.legend()
    #
    # # Save the plot to a file
    # save_dir = 'runs/plots/' + dataset_name
    # os.makedirs(save_dir, exist_ok=True)
    # plt.savefig(os.path.join(save_dir,f'{args.epochs}_epochs_{args.batch_size}_bs_{args.lr}_lr_val_plot.png'))
    # plt.show()

    print('End of training process for', dataset_name, 'dataset!')

print('All datasets processed!')
